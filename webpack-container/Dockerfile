FROM node:alpine
ENV BUILD_DIR=/node-build

RUN mkdir $BUILD_DIR
WORKDIR $BUILD_DIR

RUN apk update
RUN apk add git

COPY package.json $BUILD_DIR
RUN npm install

COPY webpack.config.js $BUILD_DIR
ENTRYPOINT ["npm", "run", "build"]
