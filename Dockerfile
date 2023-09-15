FROM python:3.11-slim

# Add dependencies
RUN mkdir -p /app /logs /config
ADD requirements.txt /requirements.txt
RUN pip3 install -r /requirements.txt

# Copy files over
ADD app /app
ADD start.sh /app

# Run
WORKDIR /app
RUN chmod +x /app/start.sh
ENTRYPOINT ["/usr/bin/sh", "/app/start.sh"]
