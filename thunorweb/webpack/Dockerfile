FROM node:24-alpine
ENV BUILD_DIR=/node-build

RUN mkdir $BUILD_DIR
WORKDIR $BUILD_DIR

RUN apk update
RUN apk add git python3 py3-setuptools make g++

COPY package.json $BUILD_DIR
RUN npm install

COPY webpack.config.js $BUILD_DIR
COPY sentry.js $BUILD_DIR
COPY plotly.js $BUILD_DIR
COPY .bootstraprc $BUILD_DIR
COPY bootstrap-customisations.scss $BUILD_DIR
ENTRYPOINT ["npm", "run", "build"]

COPY thunorweb/ $BUILD_DIR/thunor
