# alert-router — stdlib only, so there is no dependency to drift or to audit.
FROM python:3.13-alpine

RUN adduser -D -u 10001 router
WORKDIR /app
COPY router.py /app/router.py

USER router
EXPOSE 8089

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8089/health', timeout=4).status==200 else 1)"]

ENTRYPOINT ["python3", "/app/router.py"]
