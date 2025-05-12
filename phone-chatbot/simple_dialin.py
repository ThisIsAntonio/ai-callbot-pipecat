#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import argparse
import asyncio
import os
import sys

from call_connection_manager import CallConfigManager, SessionManager
from dotenv import load_dotenv
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndTaskFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyDialinSettings, DailyParams, DailyTransport
#====== IMPORTS =====
from datetime import datetime
#====== END IMPORTS =====



load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

daily_api_key = os.getenv("DAILY_API_KEY", "")
daily_api_url = os.getenv("DAILY_API_URL", "https://api.daily.co/v1")


async def main(
    room_url: str,
    token: str,
    body: dict,
):
    # ------------ CONFIGURATION AND SETUP ------------

    # Create a config manager using the provided body
    call_config_manager = CallConfigManager.from_json_string(body) if body else CallConfigManager()

    # Get important configuration values
    test_mode = call_config_manager.is_test_mode()

    # Get dialin settings if present
    dialin_settings = call_config_manager.get_dialin_settings()

    # Initialize the session manager
    session_manager = SessionManager()

    # ------------ TRANSPORT SETUP ------------

    # Set up transport parameters
    if test_mode:
        logger.info("Running in test mode")
        transport_params = DailyParams(
            api_url=daily_api_url,
            api_key=daily_api_key,
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=False,
            vad_analyzer=SileroVADAnalyzer(),
            transcription_enabled=True,
        )
    else:
        daily_dialin_settings = DailyDialinSettings(
            call_id=dialin_settings.get("call_id"), call_domain=dialin_settings.get("call_domain")
        )
        transport_params = DailyParams(
            api_url=daily_api_url,
            api_key=daily_api_key,
            dialin_settings=daily_dialin_settings,
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=False,
            vad_analyzer=SileroVADAnalyzer(),
            transcription_enabled=True,
        )

    # Initialize transport with Daily
    transport = DailyTransport(
        room_url,
        token,
        "Simple Dial-in Bot",
        transport_params,
    )

    # Initialize TTS
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
    )

    # ------------ FUNCTION DEFINITIONS ------------

    async def terminate_call(params: FunctionCallParams):
        """Function the bot can call to terminate the call upon completion of a voicemail message."""
        if session_manager:
            # Mark that the call was terminated by the bot
            session_manager.call_flow_state.set_call_terminated()

        # Then end the call
        await params.llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    # Define function schemas for tools
    terminate_call_function = FunctionSchema(
        name="terminate_call",
        description="Call this function to terminate the call.",
        properties={},
        required=[],
    )

    # Create tools schema
    tools = ToolsSchema(standard_tools=[terminate_call_function])

    # ------------ LLM AND CONTEXT SETUP ------------

    # Set up the system instruction for the LLM
    system_instruction = """You are Chatbot, a friendly, helpful robot. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way, but keep your responses brief. Start by introducing yourself. If the user ends the conversation, **IMMEDIATELY** call the `terminate_call` function. """

    # Initialize LLM
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Register functions with the LLM
    llm.register_function("terminate_call", terminate_call)

    # Create system message and initialize messages list
    messages = [call_config_manager.create_system_message(system_instruction)]

    # Initialize LLM context and aggregator
    context = OpenAILLMContext(messages, tools)
    context_aggregator = llm.create_context_aggregator(context)

    # ------------ PIPELINE SETUP ------------

    # Build pipeline
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    # Create pipeline task
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    # ------------ EVENT HANDLERS ------------
    # Call tracking variables
    call_start_time = None
    call_end_time = None
    call_terminated_reason = "unknown"

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.debug(f"First participant joined: {participant['id']}")
        await transport.capture_participant_transcription(participant["id"])
        await task.queue_frames([context_aggregator.user().get_context_frame()])
        # ==== START CALL START TIME ====
        nonlocal call_start_time
        call_start_time = datetime.now()
        # ==== END CALL START TIME ====
        
        
    # ============== SILENCE DETECTION =============
        # Silence detection
    silence_timeout = 10  # segundos
    silence_count = 0
    max_silences = 3
    silence_timer_task = None

    async def play_silence_prompt():
        nonlocal silence_count
        silence_count += 1
        logger.debug(f"Silence #{silence_count} detected. Playing TTS prompt.")

        # Play a TTS message
        await task.queue_frames(tts.create_frames("Are you still there?"))

        if silence_count >= max_silences:
            logger.debug("Maximum silence count reached. Ending call.")
            await task.queue_frames([EndTaskFrame()])

    async def silence_timer():
        await asyncio.sleep(silence_timeout)
        await play_silence_prompt()

    @transport.event_handler("on_audio")
    async def on_audio_event(transport, participant, audio_frame):
        nonlocal silence_timer_task, silence_count

        # Every time there is audio, we restart the timer
        if silence_timer_task and not silence_timer_task.done():
            silence_timer_task.cancel()

        # Reset the silence timer
        silence_timer_task = asyncio.create_task(silence_timer())

        # If the user says something, we reset the silence counter.
        if audio_frame.has_speech:
            silence_count = 0

    # ============== END SILENCE DETECTION =============

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.debug(f"Participant left: {participant}, reason: {reason}")
        
        # ======== SHOW CALL SUMMARY ========
        nonlocal call_end_time, call_terminated_reason

        call_end_time = datetime.now()
        call_terminated_reason = reason or "left"

        duration = (call_end_time -
                    call_start_time).total_seconds() if call_start_time else 0

        logger.info("=== Call Summary ===")
        logger.info(f"Start Time        : {call_start_time}")
        logger.info(f"End Time          : {call_end_time}")
        logger.info(f"Duration (s)      : {duration}")
        logger.info(f"Silence Events    : {silence_count}")
        logger.info(f"Termination Reason: {call_terminated_reason}")
        logger.info("====================")
        # ======== END CALL SUMMARY ========
        
        await task.cancel()

    # ------------ RUN PIPELINE ------------

    if test_mode:
        logger.debug("Running in test mode (can be tested in Daily Prebuilt)")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple Dial-in Bot")
    parser.add_argument("-u", "--url", type=str, help="Room URL")
    parser.add_argument("-t", "--token", type=str, help="Room Token")
    parser.add_argument("-b", "--body", type=str, help="JSON configuration string")

    args = parser.parse_args()

    # Log the arguments for debugging
    logger.info(f"Room URL: {args.url}")
    logger.info(f"Token: {args.token}")
    logger.info(f"Body provided: {bool(args.body)}")

    asyncio.run(main(args.url, args.token, args.body))
