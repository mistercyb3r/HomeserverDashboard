import {
  Activity,
  ChartColumn,
  Clapperboard,
  Cloud,
  Container,
  Cpu,
  Download,
  Home,
  Image,
  LayoutGrid,
  Radio,
  RefreshCw,
  Router,
  Server,
  Settings,
  Shield,
  Signal,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  server: Server,
  play: Clapperboard,
  satellite: Radio,
  wifi: Signal,
  box: Container,
  layout: LayoutGrid,
  download: Download,
  home: Home,
  cloud: Cloud,
  image: Image,
  cpu: Cpu,
  activity: Activity,
  shield: Shield,
  refresh: RefreshCw,
  chart: ChartColumn,
  settings: Settings,
  router: Router,
};

interface ServiceIconProps {
  name: string;
  className?: string;
}

export function ServiceIcon({ name, className = "h-4 w-4" }: ServiceIconProps) {
  const Icon = ICONS[name] ?? Server;
  return <Icon className={className} strokeWidth={1.6} />;
}
