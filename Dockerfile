FROM python:3.6
ENV PYTHONUNBUFFERED 1

ENV THUNOR_HOME=/thunor

RUN mkdir $THUNOR_HOME
WORKDIR $THUNOR_HOME
ADD requirements.txt $THUNOR_HOME
RUN pip install -r requirements.txt
CMD ["uwsgi"]
ADD manage.py $THUNOR_HOME
ADD thunordjango $THUNOR_HOME/web
ADD thunor $THUNOR_HOME/thunor
RUN cd $THUNOR_HOME/thunor && python setup.py install
ADD thunorweb $THUNOR_HOME/thunorweb
