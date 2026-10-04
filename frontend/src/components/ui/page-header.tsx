import type { ReactNode } from "react";

type PageHeaderProps = {
  actions?: ReactNode;
  description: string;
  eyebrow?: string;
  title: string;
};

export function PageHeader({ actions, description, eyebrow = "PERCEPTION WORKSPACE", title }: PageHeaderProps) {
  return <header className="editorial-header">
    <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>
    <div className="editorial-intro"><p>{description}</p>{actions ? <div className="editorial-actions">{actions}</div> : null}</div>
  </header>;
}
