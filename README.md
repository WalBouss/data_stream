# 🚀 Data Proxy Service (data-stream)

A Python-based tool that allows you to stream data from a remote server to your local compute resources. This service is particularly useful when you need to **train models on large datasets stored on a remote server but don't have sufficient storage on your local compute node**.

This repository is a wrapper around the [sshtunnel](https://github.com/pahaz/sshtunnel) library and uses [fastapi](https://fastapi.tiangolo.com/) to create a simple HTTP server to stream the data.
## ✨ Features

- 🔒 Stream data securely from a remote server using SSH tunneling
- 📝 Support for SSH config aliases and direct SSH parameters
- ⚡ FastAPI-powered HTTP endpoint for data access
- 🤖 Automatic management of remote Python HTTP server
- 🏥 Health check endpoint for monitoring
- 🔑 Support for both SSH key and password authentication
- ⚙️ Configurable ports for local and remote connections
- 🛑 Graceful shutdown handling

## 📦 Installation

Install the package using pip:

```bash
pip install data-streaming
```

Alternatively, Clone this repository:
```bash
   git clone https://github.com/yourusername/data-proxy-service.git
   cd data-proxy-service
   pip install -e .
   ```

## 🔧 Usage: Command-line Interface


To start the Data Proxy Service, use one of the following methods:

### 1. Using SSH Config Alias 📋

If you have an SSH config file (`~/.ssh/config`) with your server details:

```bash
data-stream --ssh-host-alias myserver --data-path /path/to/remote/data
```

Here is an example of an SSH config file:
```
Host myserver
    HostName example.com
    User mouloud
    IdentityFile ~/.ssh/id_rsa
```

### 2. Using Direct SSH Parameters 🔑

```bash
data-stream \
  --ssh-host example.com \
  --ssh-username myusername \
  --ssh-key-path ~/.ssh/id_rsa \
  --data-path /path/to/remote/data
```

### Optional Parameters ⚙️

- `--local-port`: Local port for SSH tunnel (default: 8000)
- `--remote-port`: Remote port for HTTP server (default: 8001)
- `--fastapi-port`: FastAPI server port (default: 5001)
- `--ssh-password`: SSH password (if not using key-based authentication)

Example with all parameters:

```bash
data-stream \
  --ssh-host example.com \
  --ssh-username john \
  --data-path /home/john/datasets \
  --ssh-key-path ~/.ssh/id_rsa \
  --local-port 8000 \
  --remote-port 8001 \
  --fastapi-port 5000
```

### 3.Using Environment Variables 🔧

You can also configure the service using environment variables:

- `PROXY_SSH_HOST_ALIAS`: SSH host alias (for SSH config)
- `PROXY_SSH_HOST`: SSH host (cluster 1)
- `PROXY_SSH_USERNAME`: SSH username
- `PROXY_DATA_PATH`: Path to data on cluster 1
- `PROXY_SSH_KEY_PATH`: Path to SSH key
- `PROXY_SSH_PASSWORD`: SSH password (if not using key)
- `PROXY_LOCAL_PORT`: Local port for SSH tunnel
- `PROXY_REMOTE_PORT`: Remote port for HTTP server
- `PROXY_FASTAPI_PORT`: FastAPI server port

## 🖥️ HPC Usage

When using data-stream on an HPC (High-Performance Computing) system:

⚠️ **Important**: Always start the service on a compute node, not on the login node. Login nodes are shared resources and aren't suitable for running services.

Example using SLURM:
```bash
#!/bin/bash
#SBATCH --job-name=data-stream
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=24:00:00

data-stream \
  --ssh-host-alias myserver \
  --data-path /path/to/remote/data
```

## 📊 Integration Examples

### WebDataset Integration 📦

data-stream works seamlessly with WebDataset for efficient data loading in machine learning pipelines:

```python
import webdataset as wds
from torch.utils.data import DataLoader

# Start data-stream service (as shown above)

# Create WebDataset pipeline
dataset = wds.WebDataset('http://localhost:5000/data/path/to/tarfiles/{000000..999999}.tar')

# Create DataLoader
dataloader = DataLoader(dataset, batch_size=None, num_workers=4)

# Use in training
for batch_input, batch_target in dataloader:
    # Your training code here
    pass
```

## 📂 Accessing Data

Once the service is running, you can access your data through:

```
http://localhost:5000/data/path/to/file
```
You can test the data stream by running:
```bash
curl http://localhost:5000/health/shard_0001.tar -o test.tar
```

## 🏥 Health Check

You can verify the service status using:

```bash
curl http://localhost:5000/health
```

This will return:
```json
{
  "status": "OK",
  "connection": {
    "hostname": "example.com",
    "username": "myusername",
    "using_ssh_config": true
  }
}
```

## 🐍 Using as a Python Package

You can also use data-stream in your Python code:

```python
from data_stream import DataProxyService, Settings

# Using SSH config alias
settings = Settings(
    ssh_host_alias="myserver",
    data_path="/path/to/remote/data"
)

# Or using direct parameters
settings = Settings(
    ssh_host="example.com",
    ssh_username="myusername",
    ssh_key_path="~/.ssh/id_rsa",
    data_path="/path/to/remote/data"
)

# Initialize and start the service
service = DataProxyService(settings)
await service.start()

# When done
await service.stop()
```

## 📋 Requirements

- Python 3.7+
- SSH access to the remote server
- Python installation on the remote server

## 🔧 Troubleshooting

### Common Issues

1. **🚫 Permission Denied**
   - Verify your username and SSH key are correct
   - Check if your user has access to the data directory on the remote server

2. **⚠️ Port Already in Use**
   - Try different ports using `--local-port`, `--remote-port`, or `--fastapi-port`
   - Check if another instance of data-stream is already running
   - On HPC, ensure no other jobs are using the same ports (that why it important to run on the compute node)

3. **🔌 Remote Server Issues**
   - Ensure Python is installed on the remote server
   - Check if the data path exists and is accessible


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.