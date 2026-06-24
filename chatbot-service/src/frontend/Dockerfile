FROM node:22-alpine AS build
WORKDIR /app
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ .
RUN npx ng build --configuration=production

FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=build /app/dist/frontend/ ./dist/frontend/
ENV PORT=4000
EXPOSE 4000
CMD ["node", "dist/frontend/server/server.mjs"]
