/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/vnc/:path*',
        destination: 'http://localhost:6080/:path*',
      },
    ]
  },
}

module.exports = nextConfig

