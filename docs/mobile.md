# Mobile

We value having a usable mobile experience, and embrace the following tools to accomplish various degrees of mobile design and interaction.

## Media Queries (Use by default)

By default, media queries should be the first thing you reach for when trying to solve mobile design problems. Responsive design using tailwind prefixes like `sm:` `md:` `lg:` benefits all screen sizes, regardless of device.

## Container Queries (Use sometimes)

You can target mobile devices specifically via the `@mobile:` tailwind prefix. Useful when accounting for mobile browser specific eccentricities like managing font sizes in inputs to prevent unwanted zoom, or ergonomics because fingers are less precise than mouse cursors and benefit from more distinguised click targets via padding and spacing. This approach doesn't yield any benefits for smalls screen on desktop browsers.
