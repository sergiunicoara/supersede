# Deploying the web demo

The demo is a read-only page over the committed **fictional** store: ask a question, see the value in
force, the reason, what it overruled, stale sources and date problems. No accounts, no API keys, no
writes, no model calls. It was built and run as a Docker image on Windows (non-root user 1000, store
files unchanged after requests); a first request answers in well under a second.

## Run it locally

```bash
python web/app.py            # http://127.0.0.1:7860
```

## Hugging Face Spaces (recommended; free for a small public app)

You need a Hugging Face account. Nothing below needs a key from this project.

1. Assemble a folder that contains exactly what the Space needs:
   ```bash
   python web/make_space.py ../supersede-space
   ```
2. On https://huggingface.co/new-space choose **SDK: Docker**, visibility **Public**, name it
   `supersede`.
3. Push the folder to the Space:
   ```bash
   cd ../supersede-space
   git init && git add . && git commit -m "Supersede demo"
   git remote add space https://huggingface.co/spaces/<your-user>/supersede
   git push space main
   ```
   (Hugging Face asks for your username and an access token with write permission when you push.)
4. Wait for the build (a few minutes). Open the Space URL, ask a question, and open it again on the
   first day of judging (12 Dec) in case a free Space has gone to sleep. Put the URL in the Devpost
   submission and the README.

## Any other Docker host (Render, Fly.io, ...)

The root `Dockerfile` listens on `$PORT` (default 7860) and needs nothing else:

```bash
docker build -t supersede-demo .
docker run -p 7860:7860 supersede-demo
```

## Rules of thumb

* Keep it fictional data only (the contest rules say not to use sensitive or real data).
* Keep it read-only, with no secrets in the image. The `ask` path is offline, so nothing here needs a key.
* It must stay up from submission until judging ends (16 Dec). Check it the day you submit.
