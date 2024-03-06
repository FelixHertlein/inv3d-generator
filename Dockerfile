FROM python:3.8-slim

RUN apt-get clean \
  && apt-get -y update \
  && apt-get -y install g++ gcc git wget unzip \
  libxtst6 libglib2.0-0 libsm6 libfontconfig1 libxrender1 libpcre3 libpcre3-dev ffmpeg poppler-utils bzip2 libglu1

RUN python -m pip install --upgrade pip

WORKDIR /tmp
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN touch /etc/default/google-chrome
RUN apt -y install ./google-chrome-stable_current_amd64.deb

RUN wget https://download.blender.org/release/Blender2.79/blender-2.79-linux-glibc219-x86_64.tar.bz2
RUN mkdir -p /usr/inv3d/blender
RUN tar -xf blender-2.79-linux-glibc219-x86_64.tar.bz2 -C /usr/inv3d/blender
ENV PATH "$PATH:/usr/inv3d/blender/blender-2.79-linux-glibc219-x86_64"

# temporary for fast rebuilding (requirements are specified in "pip install .")
RUN pip install numpy==1.20.2 tqdm==4.60.0 dpath==2.0.1 pandas==1.2.4 phonenumbers==8.12.21 Faker==8.1.1 schwifty==2021.4.0 opencv_python==4.5.1.48 bounding_box==0.1.3 scikit_learn==0.24.2 beautifulsoup4==4.9.3 pdf2image==1.14.0 selenium==3.141.0 webdriver_manager==3.4.2 pdfminer==20191125 torch==1.8.1 Flask==2.0.1
RUN pip install pillow==8.4.0
RUN pip install requests==2.26.0 Werkzeug==2.2.2

RUN mkdir -p /usr/inv3d
WORKDIR /usr/inv3d
COPY . /usr/inv3d

RUN pip install .

ENV PYTHONPATH "${PYTHONPATH}:/usr/inv3d/src"

WORKDIR /usr/inv3d
ENTRYPOINT ["python", "-u", "src/start.py"]
