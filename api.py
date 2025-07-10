import uvicorn
from fastapi import FastAPI, Request, HTTPException, Security, Depends, Header
from multiprocessing import Queue
from typing import Annotated, Optional
import json

def create_app(preshared_token: str, in_queue: Queue) -> FastAPI:
    app = FastAPI()

    # Define the security dependency using X-Auth-Token header
    async def verify_token(x_auth_token: Annotated[Optional[str], Header()] = None):
        if not x_auth_token or x_auth_token != preshared_token:
            raise HTTPException(status_code=401, detail="Invalid or missing X-Auth-Token")
        return x_auth_token

    # Define the endpoint logic
    async def handle_webhook(request: Request):
        try:
            data = await request.json()
            message = data.get("message")
            if not isinstance(message, str) or not message:
                raise HTTPException(status_code=400, detail="Invalid payload: 'message' must be a non-empty string.")
            
            in_queue.put(message)
            
            return {"status": "success", "detail": "Message queued for forwarding."}
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in request body.")

    # Determine if security is needed
    dependencies = [Depends(verify_token)] if preshared_token else []

    # Add the route to the app
    app.add_api_route(
        path="/", 
        endpoint=handle_webhook,
        methods=["POST"],
        dependencies=dependencies
    )

    return app

def run_server(host: str, port: int, webhook_path: str, token: str, in_queue: Queue):
    """
    Runs the FastAPI server with a dynamic path prefix.
    """
    # Create the base app
    app = create_app(token, in_queue)

    # Create a root app to mount the sub-app under the dynamic path
    root_app = FastAPI()
    # Ensure webhook_path doesn't have leading/trailing slashes that might break mounting
    clean_path = webhook_path.strip('/')
    root_app.mount(f"/{clean_path}", app)

    print(f"Starting FastAPI server at http://{host}:{port}/{clean_path}")
    uvicorn.run(root_app, host=host, port=port)