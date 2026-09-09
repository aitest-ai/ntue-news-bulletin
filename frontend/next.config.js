/** @type {import('next').NextConfig} */
const { withWorkflow } = require("workflow/next");

const nextConfig = {
  reactStrictMode: true,
};

module.exports = withWorkflow(nextConfig);
