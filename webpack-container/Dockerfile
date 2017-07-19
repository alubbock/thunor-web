FROM node:alpine
ENV BUILD_DIR=/node-build

RUN mkdir $BUILD_DIR
WORKDIR $BUILD_DIR

RUN apk update
RUN apk add git

COPY package.json $BUILD_DIR
RUN npm install

COPY webpack.config.js $BUILD_DIR
COPY plotly.js $BUILD_DIR
COPY .bootstraprc $BUILD_DIR
COPY bootstrap-customisations.scss
ENTRYPOINT ["npm", "run", "build"]
