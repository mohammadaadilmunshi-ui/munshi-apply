const validHostedApplicationId = /^application-[A-Za-z0-9-]{8,120}$/;

export function isHostedApplicationSelected(applicationId: string): boolean {
  return validHostedApplicationId.test(applicationId);
}
