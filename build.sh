# Stop and remove the existing combined container (if it exists)
docker stop spacebot_combined
docker rm spacebot_combined

# Build the Docker image
docker build -t spacebot_combined .

# Ensure the data directory exists
mkdir -p /data/dockerData/spaceBot

# Run the Docker container, mounting the host directory for storage
docker run --restart=unless-stopped -d -p 2000:2000 --name spacebot_combined -v /data/dockerData/spaceBot:/data/dockerData/spaceBot spacebot_combined