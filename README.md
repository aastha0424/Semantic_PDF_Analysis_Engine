# Challenge 1b: Multi-Collection PDF Analysis
---

## How to Run with Docker
This project is containerized with Docker for easy and consistent execution.

---
### Prerequisites
- Docker Desktop must be installed and running.

---
### Step 1: Build the Docker Image

You can build the Docker image in two ways: from your local files or directly from a GitHub repository.

---
#### Option A: Build from Local Files

Open your terminal (PowerShell, Command Prompt, etc.),  
navigate to the `Challenge_1b` project directory,  
and run:

```bash
docker build -t challenge1b-solution .
```

---
#### Option B: Build from GitHub

This command downloads the repository and builds the image from the Dockerfile.
Replace with your GitHub repo URL:

```bash
docker build -t challenge1b-github https://github.com/aastha0424/Team_AiVengers_Challenge_1b
```
---
### Step 2: Run the Analysis

The command below runs the application.  
The `-v` flag maps your local folder to `/app/data` inside the container.

---
#### Run with Sample Collections

To run analysis on a sample collection like `Collection_3`, run:

```bash
docker run --rm -v "$(pwd)/Collection_3:/app/data" challenge1b-solution
```

To run on `Collection_1` or `Collection_2`, just change the folder name in the command.

> Output: `challenge1b_output.json` will be saved in the same folder you provided.

---
### Run with Your Own Custom Input (For Judges)

Follow these steps to run with a new custom set of documents.

---
#### Prepare Your Input Folder

Create a folder (e.g., `My_Test_Collection`) containing:

- A `challenge1b_input.json` file defining persona & task.
- A subfolder named `PDFs/` with all your PDF documents.

**Example Structure:**
```
My_Test_Collection/
├── challenge1b_input.json
└── PDFs/
    ├── doc1.pdf
    └── doc2.pdf
```

---
#### Run the Container with Your Folder

Use this command (replace with your folder name):

```bash
docker run --rm -v "$(pwd)/My_Test_Collection:/app/data" challenge1b-solution
```

> The script will generate `challenge1b_output.json` inside your `My_Test_Collection` folder.

---

