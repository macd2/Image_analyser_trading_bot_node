/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Use Railway private domain if available, otherwise localhost
    const vncHost = process.env.RAILWAY_PRIVATE_DOMAIN || 'localhost';
    const vncPort = process.env.VNC_PORT || '6080';

    return [
      {
        source: '/vnc/:path*',
        destination: `http://${vncHost}:${vncPort}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig

