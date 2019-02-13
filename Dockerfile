FROM python:3.6.0-slim
RUN pip install hug
RUN apt-get update
RUN apt-get -y install openssh-client
RUN cd /root
RUN mkdir /root/.ssh
RUN sed -i 's/GSSAPI/#GSSAPI/g' /etc/ssh/ssh_config
CMD hug -f /hug/apiserver.py
