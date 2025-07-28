# --- Build Stage ---
# This stage installs all dependencies
FROM python:3.9-slim AS builder

WORKDIR /app

# Step 1: Update and install system dependencies (like gcc)
RUN apt-get update && apt-get install -y build-essential

# Step 2: Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: Clean up unnecessary system files to keep the layer small
RUN apt-get purge -y --auto-remove build-essential && rm -rf /var/lib/apt/lists/*


# --- Final, Secure Stage ---
# Start from a fresh, minimal python image
FROM python:3.9-slim

WORKDIR /app

# --- FIX: Use the correct command to create the user and home directory ---
RUN addgroup --system nonroot && adduser --system --ingroup nonroot --home /home/nonroot nonroot

# Copy only your application's source code
COPY src/ ./src

# Copy the installed Python libraries from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# Switch to the non-root user
USER nonroot

# Set the HOME environment variable for the non-root user
ENV HOME=/home/nonroot

# Set the command to run when the container starts
CMD ["python", "src/main.py"]