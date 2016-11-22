Thunor
======

Deployment
----------

First, set up the site-specific configuration:

_conf/thunor.env - Environment variable configuration
_conf/nginx.conf - nginx configuration

Symbolic link the nginx.conf:

    ln -s /etc/nginx/sites-enabled/thunor `pwd`/_conf/nginx.conf

Then, just bring up the Docker containers:

    docker-compose up
