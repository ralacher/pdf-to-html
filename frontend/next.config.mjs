/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  compiler: {
    styledComponents: false,
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    return [
      {
        // Proxy all /api/* requests to the backend EXCEPT /api/preview/*,
        // which is handled by Next.js's own API route (preview proxy).
        source: '/api/:path((?!preview/).*)',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
