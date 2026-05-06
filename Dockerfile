# Base image
FROM python:3.9

# Set the timezone to America/New_York
RUN ln -sf /usr/share/zoneinfo/America/New_York /etc/localtime

# Set the working directory inside the container
WORKDIR /app

# Create data directory
RUN mkdir -p /app/data

# Copy the requirements.txt file
COPY requirements.txt .

# Install the Python dependencies
RUN pip install -r requirements.txt

# Copy the application code into the container
COPY . .

# Copy the .env file
COPY .env /app/.env

# Expose the port on which the Flask app will run
EXPOSE 5000

# Run the application
CMD ["python", "main.py"]