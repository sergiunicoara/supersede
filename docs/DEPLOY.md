# Deploying the web demo

The demo is a read-only page over the committed **fictional** store: ask a question, see the value in
force, the reason, what it overruled, stale sources and date problems. No accounts, no API keys, no
writes, no model calls. It was built and run as a Docker image on Windows (non-root user 1000, store
files unchanged after requests); a first request answers in well under a second.

## Run it locally

```bash
python web/app.py            # http://127.0.0.1:7860
```

## Render (used for the live demo; free web service)

The live demo, https://supersede-demo.onrender.com, is a free Render web service built from this repository's
`Dockerfile`: **New > Web Service > Public Git Repository**, the repo URL, language Docker, branch `main`, and the
**Free** instance type (check it: the default is a paid plan). Nothing else to set; no keys. A free instance spins down
after 15 minutes without traffic and takes about a minute to wake, and all free services in a Render workspace share
750 instance hours a month. Open it shortly before judging so it is awake.

## Hugging Face Spaces (not used)

The Docker SDK is a paid feature on a free Hugging Face account, and the free tier only runs Gradio apps, so the demo
is not hosted there. `web/make_space.py` still assembles a Docker-SDK Space folder if you have a plan that allows it.

## Any other Docker host (Render, Fly.io, ...)

The root `Dockerfile` listens on `$PORT` (default 7860) and needs nothing else:

```bash
docker build -t supersede-demo .
docker run -p 7860:7860 supersede-demo
```

## Rules of thumb

* Keep it fictional data only (the contest rules say not to use sensitive or real data).
* Keep it read-only, with no secrets in the image. The `ask` path is offline, so nothing here needs a key.
* It must stay up from submission until judging ends (16 Dec). Check it the day you submit, and again on 12 Dec.
