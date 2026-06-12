This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

## Styling (Tailwind CSS v4)

- **PostCSS:** `postcss.config.mjs` runs `@tailwindcss/postcss`.
- **Entry:** `src/app/globals.css` imports Tailwind (`@import "tailwindcss";`), then keeps the product design system in `@layer base` (tokens, resets, typography, `main`) and `@layer components` (panels, nav, auth, scorecard, etc.). Use Tailwind utilities in JSX alongside these classes (for example `className="panel flex gap-4"`).
- **Tokens:** Colours and spacing stay on `:root` CSS variables (`--space-*`, `--cauvery`, …) so existing screens stay visually identical.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
