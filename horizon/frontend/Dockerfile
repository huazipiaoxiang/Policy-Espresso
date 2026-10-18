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
ENV NEXT_PUBLIC_API_BASE=http://api:8000/api/v1
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
