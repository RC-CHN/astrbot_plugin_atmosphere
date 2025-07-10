import uvicorn
from fastapi import FastAPI, Request, HTTPException
import json

app = FastAPI()

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
        print("===== Webhook Received =====")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("============================")
        return {"status": "success", "data_received": data}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Listening for webhooks at http://0.0.0.0:8000/webhook")
    uvicorn.run(app, host="0.0.0.0", port=8000)