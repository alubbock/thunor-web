FROM python:3.6
ENV PYTHONUNBUFFERED 1

ENV THUNOR_HOME=/thunor

RUN mkdir $THUNOR_HOME
WORKDIR $THUNOR_HOME
ADD requirements.txt $THUNOR_HOME
RUN pip install -r requirements.txt
CMD ["uwsgi"]
ADD manage.py $THUNOR_HOME
ADD web $THUNOR_HOME/web
ADD pydrc $THUNOR_HOME/pydrc
RUN cd $THUNOR_HOME/pydrc && python setup.py install
ADD pyhts $THUNOR_HOME/pyhts
