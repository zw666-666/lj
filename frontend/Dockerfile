# 阶段一：构建
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json .
RUN npm config set registry https://registry.npmmirror.com && npm install --legacy-peer-deps
COPY . .
RUN npm run build

# 阶段二：nginx 托管
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
