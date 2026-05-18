FROM nginx:1.27-alpine
LABEL description="FTTH GIS Route Planner"
RUN rm -rf /usr/share/nginx/html/*
COPY index.html    /usr/share/nginx/html/
COPY manifest.json /usr/share/nginx/html/
COPY sw.js         /usr/share/nginx/html/
COPY assets/       /usr/share/nginx/html/assets/
COPY nginx.conf    /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=30s CMD wget -q --spider http://localhost/ || exit 1
EXPOSE 80
CMD ["nginx","-g","daemon off;"]
