FROM node:22-alpine AS builder

WORKDIR /app

# Build context is the repository root so the landing page (index.html)
# can be shipped together with the dashboard.
COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ .

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build


FROM nginx:alpine

# React dashboard is served under /dashboard.
COPY --from=builder /app/dist /usr/share/nginx/html/dashboard

# Landing page is the main screen at /.
COPY index.html /usr/share/nginx/html/index.html

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
