import os
import argparse
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from sshtunnel import SSHTunnelForwarder
import paramiko
import logging
import signal
import sys
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
from dataclasses import dataclass


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # SSH connection settings - either alias or direct details
    ssh_host_alias: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_key_path: Optional[str] = None
    
    # Common settings
    data_path: str
    local_port: int = 8000
    remote_port: int = 8001
    fastapi_port: int = 5000
    
    class Config:
        env_prefix = "PROXY_"


@dataclass
class SSHConfig:
    hostname: str
    username: str
    key_filename: Optional[str] = None
    port: int = 22


class SSHConfigProvider:
    def __init__(self):
        self.ssh_config = paramiko.SSHConfig()
        self._load_ssh_config()

    def _load_ssh_config(self):
        ssh_config_path = Path.home() / '.ssh' / 'config'
        if ssh_config_path.exists():
            with open(ssh_config_path) as f:
                self.ssh_config.parse(f)
        else:
            logger.warning("No SSH config file found at ~/.ssh/config")

    def get_ssh_config(self, host_alias: str) -> SSHConfig:
        host_config = self.ssh_config.lookup(host_alias)
        return SSHConfig(
            hostname=host_config.get('hostname', host_alias),
            username=host_config.get('user'),
            key_filename=host_config.get('identityfile', [None])[0],
            port=int(host_config.get('port', 22))
        )


app = FastAPI(title="Data Proxy Service")


class DataProxyService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tunnel = None
        self.ssh_client = None
        self.client = httpx.AsyncClient()
        self.ssh_config_provider = SSHConfigProvider()
        self.ssh_config = self._get_ssh_config()

    def _get_ssh_config(self) -> SSHConfig:
        if self.settings.ssh_host_alias:
            # Use SSH config file
            logger.info(f"Using SSH config alias: {self.settings.ssh_host_alias}")
            return self.ssh_config_provider.get_ssh_config(self.settings.ssh_host_alias)
        else:
            # Use direct SSH parameters
            logger.info("Using direct SSH parameters")
            return SSHConfig(
                hostname=self.settings.ssh_host,
                username=self.settings.ssh_username,
                key_filename=self.settings.ssh_key_path
            )

    async def start(self):
        try:
            logger.info(f"Connecting using SSH config: {self.ssh_config}")
            
            # Start SSH tunnel
            self.tunnel = SSHTunnelForwarder(
                self.ssh_config.hostname,
                ssh_username=self.ssh_config.username,
                ssh_pkey=self.ssh_config.key_filename,
                ssh_port=self.ssh_config.port,
                remote_bind_address=('127.0.0.1', self.settings.remote_port),
                local_bind_address=('127.0.0.1', self.settings.local_port)
            )
            self.tunnel.start()

            # Start HTTP server on remote host
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.ssh_config.hostname,
                username=self.ssh_config.username,
                key_filename=self.ssh_config.key_filename,
                port=self.ssh_config.port
            )
            
            # Kill any existing Python HTTP servers on the remote port
            self.ssh_client.exec_command(f"pkill -f 'python -m http.server {self.settings.remote_port}'")
            
            # Start a new HTTP server in the background
            cmd = f"cd {self.settings.data_path} && python3 -m http.server {self.settings.remote_port} > /dev/null 2>&1 &"
            self.ssh_client.exec_command(cmd)
            
            logger.info(f"Data proxy service started. Access data at http://localhost:{self.settings.fastapi_port}/data/")
            
        except Exception as e:
            logger.error(f"Failed to start data proxy service: {e}")
            await self.stop()
            raise

    async def stop(self):
        await self.client.aclose()
        if self.ssh_client:
            self.ssh_client.close()
        if self.tunnel:
            self.tunnel.stop()


# Global service instance
proxy_service = None

@app.on_event("startup")
async def startup_event():
    global proxy_service
    settings = Settings()
    proxy_service = DataProxyService(settings)
    await proxy_service.start()

@app.on_event("shutdown")
async def shutdown_event():
    if proxy_service:
        await proxy_service.stop()

@app.get("/data/{filename:path}")
async def proxy_data(filename: str):
    try:
        url = f'http://127.0.0.1:{proxy_service.settings.local_port}/{filename}'
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="File not found")
            
            async def iterfile():
                async for chunk in response.aiter_bytes():
                    yield chunk

            return StreamingResponse(
                iterfile(),
                media_type=response.headers.get('content-type'),
                headers={k: v for k, v in response.headers.items() if k.lower() != 'content-length'}
            )
    except httpx.HTTPError as e:
        logger.error(f"Error proxying data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    ssh_config = proxy_service.ssh_config
    return {
        "status": "OK",
        "connection": {
            "hostname": ssh_config.hostname,
            "username": ssh_config.username,
            "using_ssh_config": proxy_service.settings.ssh_host_alias is not None
        }
    }

def signal_handler(sig, frame):
    logger.info("Shutting down gracefully...")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Start data proxy service')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--ssh-host-alias', help='SSH host alias from ~/.ssh/config')
    group.add_argument('--ssh-host', help='SSH hostname')
    
    parser.add_argument('--ssh-username', help='SSH username (required if using --ssh-host)')
    parser.add_argument('--ssh-key-path', help='Path to SSH key (optional if using --ssh-host)')
    parser.add_argument('--data-path', required=True, help='Path to data on remote server')
    parser.add_argument('--local-port', type=int, default=8000, help='Local port for SSH tunnel')
    parser.add_argument('--remote-port', type=int, default=8001, help='Remote port for HTTP server')
    parser.add_argument('--fastapi-port', type=int, default=5001, help='FastAPI server port')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.ssh_host and not args.ssh_username:
        parser.error("--ssh-username is required when using --ssh-host")
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set environment variables for settings
    if args.ssh_host_alias:
        os.environ["PROXY_SSH_HOST_ALIAS"] = args.ssh_host_alias
    else:
        os.environ["PROXY_SSH_HOST"] = args.ssh_host
        os.environ["PROXY_SSH_USERNAME"] = args.ssh_username
        if args.ssh_key_path:
            os.environ["PROXY_SSH_KEY_PATH"] = args.ssh_key_path
    
    os.environ["PROXY_DATA_PATH"] = args.data_path
    os.environ["PROXY_LOCAL_PORT"] = str(args.local_port)
    os.environ["PROXY_REMOTE_PORT"] = str(args.remote_port)
    os.environ["PROXY_FASTAPI_PORT"] = str(args.fastapi_port)
    
    # Run the FastAPI app with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.fastapi_port)
if __name__ == "__main__":
    main()
    
    