# Get Linux
FROM alpine:3.14

# Get Java via the package manager
RUN apk update \
&& apk upgrade \
&& apk add --no-cache bash \
&& apk add --no-cache --virtual=build-dependencies unzip \
&& apk add --no-cache curl \
&& apk add --no-cache openjdk8-jre

# Get Python, PIP
RUN apk add --no-cache python3 \
&& python3 -m ensurepip \
&& pip3 install --upgrade pip setuptools \
&& rm -r /usr/lib/python*/ensurepip && \
if [ ! -e /usr/bin/pip ]; then ln -s pip3 /usr/bin/pip ; fi && \
if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3 /usr/bin/python; fi && \
rm -r /root/.cache

# Copy application code
COPY . /app

# set up working directory
WORKDIR /app

# Install community version of pandas, since listing it in requirement.txt takes forever to build
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/v3.14/community" >> /etc/apk/repositories && \
    apk --no-cache add py3-pandas@community

# Install Python dependencies
RUN pip install -r requirements.txt

# Set the entry point for running the appliation - for deploying to cloud
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app", "-w", "1", "--threads", "6", "--log-level" , "debug", "-t", "100"]


# # Set the entry point for running the application
# CMD python app.py


