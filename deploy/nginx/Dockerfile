FROM node:22.14.0-alpine@sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944 AS frontend-build

WORKDIR /opt/ux09-frontend
COPY package.json package-lock.json ./
RUN npm ci --fund=false --audit=false
COPY index.html vite.config.js vite.config.mjs ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284

COPY --from=frontend-build /opt/ux09-frontend/dist /usr/share/nginx/html
