# ai-callbot-pipecat

An AI-powered voice assistant built from the [Pipecat Phone Chatbot example](https://github.com/pipecat-ai/pipecat/tree/main/examples/phone-chatbot) as a response to the Adventis AI Software Engineer challenge.

## 📌 Summary for Adventis

This project addresses the Adventis AI Engineer Challenge by:

- ✅ Forking and customizing the `phone-chatbot` example from Pipecat
- ✅ Running inbound calls using Daily test mode (no ngrok needed)
- ✅ Detecting 10s of user silence using Silero VAD
- ✅ Triggering a TTS prompt after each silence
- ✅ Gracefully terminating the call after 3 unanswered silences
- ✅ Logging a summary of the call: start/end time, duration, silence count, reason

🛠 Built in <48 hours from scratch, using Python, FastAPI, and Daily APIs. Ready for extension or production deployment.

## 🚀 Features Implemented

✅ Inbound call support via Daily (testInPrebuilt)  
✅ Silence detection using Silero VAD  
✅ TTS prompt after 10+ seconds of silence (via Cartesia)  
✅ Graceful termination after 3 unanswered silence prompts  
✅ Post-call summary with stats (duration, silence events, etc.)  

---

## 🧠 How it works

- Runs locally using `FastAPI` and exposes a `/start` endpoint for test or webhook usage.
- Uses Daily to join a room as a bot.
- Detects silence using `SileroVADAnalyzer`.
- Plays a prompt like "Are you still there?" via Cartesia TTS.
- Ends the call after 3 unacknowledged prompts.
- Logs summary info (duration, silence count, reason).

---

## 🧪 How to Test (Local Mode)

> Requires Python 3.10+ and `virtualenv`

```bash
git clone https://github.com/yourusername/ai-callbot-pipecat.git
cd ai-callbot-pipecat
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

pip install -r phone-chatbot/requirements.txt

# Add your credentials in a .env file in the root folder
```

Sample `.env`:

```env
DAILY_SAMPLE_ROOM_URL=https://your-team.daily.co/testroom
DAILY_API_KEY=your_real_api_key
DAILY_API_URL=https://api.daily.co/v1
OPENAI_API_KEY=dummy
CARTESIA_API_KEY=dummy
```

---

### ▶️ Run locally (test mode)

```bash
python phone-chatbot/simple_dialin.py -u "https://your-team.daily.co/testroom" -t "" -b "{\"config\": {\"simple_dialin\": {\"testInPrebuilt\": true}}}"
```

Then open the room in your browser and speak. Stay silent for 10+ seconds to trigger a prompt.

---

## ⚠️ Notes

- Some modules (`daily`, `onnxruntime`, `cartesia`) may require Linux or macOS for full compatibility due to build toolchain limitations on Windows.
- If installing fails, recommend using WSL or testing on a Mac.

---

## 📬 Challenge context

This was implemented as a weekend/hackathon-style challenge for a role at **Adventis**, based on:

> https://github.com/pipecat-ai/pipecat/tree/main/examples/phone-chatbot  
> _“Implement silence detection, prompt, graceful call termination and summary logging.”_

---

## 📄 License

Based on original code licensed under BSD-2-Clause License by Daily.