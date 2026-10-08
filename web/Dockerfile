FROM node:22-alpine AS build

WORKDIR /app
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM nginx:1.27-alpine
ARG FRONTEND_DIST=dist
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/${FRONTEND_DIST} /usr/share/nginx/html
EXPOSE 80
