# Base image
FROM python:3.9

# Set the timezone to America/New_York
RUN ln -sf /usr/share/zoneinfo/America/New_York /etc/localtime

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt file
COPY requirements.txt .

# Install the Python dependencies
RUN pip install -r requirements.txt

# Copy the SpaceBot code into the container
COPY . .

# Run the SpaceBot script
CMD ["python", "spaceBot.py"]
