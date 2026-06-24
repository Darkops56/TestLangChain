import { APP_BASE_HREF } from '@angular/common';
import { CommonEngine, isMainModule } from '@angular/ssr/node';
import express from 'express';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { request as httpRequest } from 'node:http';
import bootstrap from './main.server';

const serverDistFolder = dirname(fileURLToPath(import.meta.url));
const browserDistFolder = resolve(serverDistFolder, '../browser');
const indexHtml = join(serverDistFolder, 'index.server.html');

const app = express();
const commonEngine = new CommonEngine();

// Set Permissions-Policy to explicitly allow microphone access on the same origin
app.use((_req, res, next) => {
  res.setHeader('Permissions-Policy', 'microphone=(self)');
  next();
});

/**
 * Proxy /api and /hubs requests to the .NET backend.
 * In Docker Compose the backend service is reachable at http://backend:5000.
 * For local dev outside Docker, override BACKEND_URL env var.
 */
const backendUrl = new URL(process.env['BACKEND_URL'] || 'http://backend:5000');

app.all('/api/*', (req, res) => {
  const proxyReq = httpRequest(
    {
      hostname: backendUrl.hostname,
      port: backendUrl.port || 5000,
      path: req.originalUrl,
      method: req.method,
      headers: { ...req.headers, host: `${backendUrl.hostname}:${backendUrl.port || 5000}` },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    },
  );
  proxyReq.on('error', () => res.status(502).json({ error: 'Backend unavailable' }));
  req.pipe(proxyReq, { end: true });
});

app.all('/hubs/*', (req, res) => {
  const proxyReq = httpRequest(
    {
      hostname: backendUrl.hostname,
      port: backendUrl.port || 5000,
      path: req.originalUrl,
      method: req.method,
      headers: { ...req.headers, host: `${backendUrl.hostname}:${backendUrl.port || 5000}` },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    },
  );
  proxyReq.on('error', () => res.status(502).json({ error: 'Backend unavailable' }));
  req.pipe(proxyReq, { end: true });
});

/**
 * Serve static files from /browser
 */
app.get(
  '**',
  express.static(browserDistFolder, {
    maxAge: '1y',
    index: 'index.html'
  }),
);

/**
 * Handle all other requests by rendering the Angular application.
 */
app.get('**', (req, res, next) => {
  const { protocol, originalUrl, baseUrl, headers } = req;

  commonEngine
    .render({
      bootstrap,
      documentFilePath: indexHtml,
      url: `${protocol}://${headers.host}${originalUrl}`,
      publicPath: browserDistFolder,
      providers: [{ provide: APP_BASE_HREF, useValue: baseUrl }],
    })
    .then((html) => res.send(html))
    .catch((err) => next(err));
});

/**
 * Start the server if this module is the main entry point.
 * The server listens on the port defined by the `PORT` environment variable, or defaults to 4000.
 */
if (isMainModule(import.meta.url)) {
  const port = process.env['PORT'] || 4000;
  app.listen(port, () => {
    console.log(`Node Express server listening on http://localhost:${port}`);
  });
}

export default app;
