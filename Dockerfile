FROM python:3.7.2-slim
RUN pip install hug
COPY apiserver.py /
CMD hug -f /apiserver.py
