/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // VNC server runs in the same container via supervisor, so use localhost
    const vncHost = 'localhost';
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

