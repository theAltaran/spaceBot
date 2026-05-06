# Stop and remove the existing combined container (if it exists)
docker stop spacebot_combined
docker rm spacebot_combined

# Build the Docker image
docker build -t spacebot_combined .

# Create the Docker volume if it doesn't exist
docker volume create spacebot_combined

# Run the Docker container, using the volume for storage
docker run --restart=unless-stopped -d -p 5000:5000 --name spacebot_combined -v spacebot_combined:/app/data spacebot_combined