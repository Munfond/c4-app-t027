FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
# Only simulation media is approved for the initial deployment.
# Keep unreviewed public/lab camera composites out of the runtime image entirely.
COPY --from=build --chown=node:node /app/public/sim ./public/sim
COPY --from=build --chown=node:node /app/public/next.svg /app/public/vercel.svg ./public/
USER node
EXPOSE 3000
CMD ["node", "server.js"]
