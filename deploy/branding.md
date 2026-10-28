# Product Branding Assets

Edit `branding.json` for the deployed product display identity. The current
configuration is `Ji Guang`, short name `JG`, with `/branding/logo.svg` as the
logo and favicon. This does not rename Aurora, its email sender identity, any
database, deployment directory, repository or cryptographic identifier.

`name` is a trimmed display name (1-80 characters); `short_name` contains 1-8
ASCII letters/digits. `logo_url` and optional `favicon_url` are same-origin
absolute paths, without query strings, fragments, backslashes or traversal.
Use `null` for a generated short-name monogram. Image files in `deploy/branding/`
are served under `/branding/`; keep non-image files outside that directory.
Use a new asset filename when replacing an image so
browser image caches cannot keep the old mark.

The release packages this JSON and the assets together, mounting the identical
JSON read-only into proxy, API and worker. Changing this configuration requires
a normal authorized release; it is not an edit to the running server. Brand
changes require all application containers to be recreated. Rollback uses the
selected release's own branding files. Old releases without branding artifacts
continue to use their original release configuration.

The public product remains the canonical source. Publish the reviewed public
branding support and update the private `product` submodule before deployment;
do not patch an older pinned product independently.
