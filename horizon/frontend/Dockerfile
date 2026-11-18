FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* 在构建期内联，Docker 环境下必须指向容器名 api（非 localhost）
ARG NEXT_PUBLIC_API_BASE=http://api:8000/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
# next.config 使用 output: "standalone"，`next start` 与之不兼容（见 prod.err 警告）。
# standalone 已产出最小化生产服务器 server.js，只需补上静态资源，再用 node 直接启动。
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
