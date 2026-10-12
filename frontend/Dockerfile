FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN --mount=type=secret,id=cloud-ca if [ -f /run/secrets/cloud-ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/cloud-ca; fi; npm ci
COPY . .
RUN npm run build
FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY --chown=101:101 --from=build /app/dist /usr/share/nginx/html
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
