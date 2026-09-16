declare module "virtual:core-connection" {
  import type { CoreConnection } from "@livingworld/api-client";
  const connection: CoreConnection | null;
  export default connection;
}
