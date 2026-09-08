"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { PanelLeftIcon } from "lucide-react";

import {
  SidebarContext,
  type SidebarContextProps,
  useSidebar,
} from "./sidebar-context";
import { useIsMobile } from "./use-mobile";
import { cn } from "./utils";
import { Button } from "./button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "./sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

const SIDEBAR_WIDTH = "var(--ui-layout-sidebar-width)";
const SIDEBAR_WIDTH_MOBILE = "var(--ui-layout-sidebar-width-mobile)";
const SIDEBAR_WIDTH_COLLAPSED = "var(--ui-layout-sidebar-collapsed)";

function SidebarProvider({
  className,
  style,
  children,
  ...props
}: React.ComponentProps<"div">) {
  const isMobile = useIsMobile();
  const [open, setOpen] = React.useState(true);
  const [openMobile, setOpenMobile] = React.useState(false);

  const contextValue = React.useMemo<SidebarContextProps>(
    () => ({
      isMobile,
      open,
      openMobile,
      setOpen,
      setOpenMobile,
    }),
    [isMobile, open, openMobile],
  );

  return (
    <SidebarContext.Provider value={contextValue}>
      <TooltipProvider delayDuration={0}>
        <div
          data-slot="sidebar-wrapper"
          style={
            {
              "--sidebar-width": SIDEBAR_WIDTH,
              "--sidebar-width-collapsed": SIDEBAR_WIDTH_COLLAPSED,
              ...style,
            } as React.CSSProperties
          }
          className={cn(
            "flex h-svh w-full overflow-hidden bg-ui-canvas has-data-[variant=inset]:bg-sidebar",
            className,
          )}
          {...props}
        >
          {children}
        </div>
      </TooltipProvider>
    </SidebarContext.Provider>
  );
}

function Sidebar({
  side = "left",
  variant = "sidebar",
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  side?: "left" | "right";
  variant?: "sidebar" | "floating" | "inset";
}) {
  const { isMobile, open, openMobile, setOpenMobile } = useSidebar();

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile} {...props}>
        <SheetContent
          data-sidebar="sidebar"
          data-slot="sidebar"
          data-mobile="true"
          className="bg-sidebar text-sidebar-foreground w-(--sidebar-width) p-0 [&>button]:hidden"
          style={
            {
              "--sidebar-width": SIDEBAR_WIDTH_MOBILE,
            } as React.CSSProperties
          }
          side={side}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Sidebar</SheetTitle>
            <SheetDescription>Displays the mobile sidebar.</SheetDescription>
          </SheetHeader>
          <div className="flex h-full w-full flex-col">{children}</div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <div
      className="peer text-sidebar-foreground hidden md:block"
      data-state={open ? "expanded" : "collapsed"}
      data-variant={variant}
      data-side={side}
      data-slot="sidebar"
    >
      <div
        data-slot="sidebar-gap"
        className={cn(
          "transition-[width] duration-200 ease-out",
          open
            ? variant === "floating"
              ? "w-[calc(var(--sidebar-width)+1rem)]"
              : variant === "inset"
                ? "w-(--sidebar-width)"
                : "w-(--sidebar-width)"
            : variant === "floating"
              ? "w-[calc(var(--sidebar-width-collapsed)+1rem)]"
              : variant === "inset"
                ? "w-(--sidebar-width-collapsed)"
                : "w-(--sidebar-width-collapsed)",
        )}
      />
      <div
        data-slot="sidebar-container"
        className={cn(
          "fixed inset-y-0 z-10 hidden h-svh transition-[width] duration-200 ease-out md:flex",
          open ? "w-(--sidebar-width)" : "w-(--sidebar-width-collapsed)",
          side === "left" ? "left-0" : "right-0",
          variant === "floating"
            ? "p-1.5"
            : variant === "inset"
              ? side === "left"
                ? "py-2 pl-2 pr-0"
                : "py-2 pl-0 pr-2"
              : side === "left"
                ? "border-r"
                : "border-l",
          className,
        )}
        {...props}
      >
        <div
          data-sidebar="sidebar"
          data-slot="sidebar-inner"
          className="flex h-full w-full flex-col border-sidebar-border/70 bg-sidebar/95 shadow-ui-sm backdrop-blur-xl group-data-[variant=floating]:rounded-xl group-data-[variant=floating]:border group-data-[variant=inset]:rounded-xl group-data-[variant=inset]:border"
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function SidebarInset({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-inset"
      className={cn(
        "relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-ui-canvas",
        "md:peer-data-[variant=inset]:my-2 md:peer-data-[variant=inset]:mr-2 md:peer-data-[variant=inset]:rounded-r-xl md:peer-data-[variant=inset]:rounded-l-none md:peer-data-[variant=inset]:border md:peer-data-[variant=inset]:border-border/70 md:peer-data-[variant=inset]:bg-background md:peer-data-[variant=inset]:shadow-ui-sm",
        className,
      )}
      {...props}
    />
  );
}

function SidebarTrigger({
  className,
  onClick,
  ...props
}: React.ComponentProps<typeof Button>) {
  const { isMobile, setOpen, setOpenMobile } = useSidebar();

  return (
    <Button
      className={cn("size-8", className)}
      data-sidebar="trigger"
      data-slot="sidebar-trigger"
      onClick={(event) => {
        onClick?.(event);

        if (event.defaultPrevented) {
          return;
        }

        if (isMobile) {
          setOpenMobile(true);
          return;
        }

        setOpen((open) => !open);
      }}
      size="icon"
      type="button"
      variant="ghost"
      {...props}
    >
      <PanelLeftIcon className="size-4" />
      <span className="sr-only">Open sidebar</span>
    </Button>
  );
}

function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-header"
      data-sidebar="header"
      className={cn("flex flex-col gap-1.5 p-1.5", className)}
      {...props}
    />
  );
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-footer"
      data-sidebar="footer"
      className={cn(
        "flex flex-col gap-1.5 border-t border-sidebar-border p-1.5",
        className,
      )}
      {...props}
    />
  );
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-content"
      data-sidebar="content"
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-1 overflow-auto py-1",
        className,
      )}
      {...props}
    />
  );
}

function SidebarGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-group"
      data-sidebar="group"
      className={cn(
        "relative flex w-full min-w-0 flex-col px-1.5 py-1",
        className,
      )}
      {...props}
    />
  );
}

function SidebarGroupLabel({
  className,
  asChild = false,
  ...props
}: React.ComponentProps<"div"> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "div";

  return (
    <Comp
      data-slot="sidebar-group-label"
      data-sidebar="group-label"
      className={cn(
        "flex h-6 shrink-0 items-center rounded-md px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-sidebar-foreground/60 outline-hidden ring-sidebar-ring focus-visible:ring-2 [&>svg]:size-4 [&>svg]:shrink-0",
        className,
      )}
      {...props}
    />
  );
}

function SidebarGroupContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-group-content"
      data-sidebar="group-content"
      className={cn("w-full text-sm", className)}
      {...props}
    />
  );
}

function SidebarMenu({ className, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="sidebar-menu"
      data-sidebar="menu"
      className={cn("flex w-full min-w-0 flex-col gap-0.5", className)}
      {...props}
    />
  );
}

function SidebarMenuItem({ className, ...props }: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="sidebar-menu-item"
      data-sidebar="menu-item"
      className={cn("group/menu-item relative", className)}
      {...props}
    />
  );
}

const sidebarMenuButtonVariants = cva(
  "peer/menu-button relative flex w-full items-center gap-2 overflow-hidden rounded-lg px-2.5 py-1.5 text-left text-sm outline-hidden ring-sidebar-ring transition-[background-color,color,box-shadow] duration-[var(--ui-motion-duration-base)] ease-[var(--ui-motion-ease-standard)] before:absolute before:inset-y-1.5 before:left-1 before:w-0.5 before:rounded-full before:bg-sidebar-primary before:opacity-0 before:transition-opacity before:content-[''] hover:bg-sidebar-accent/80 hover:text-sidebar-accent-foreground focus-visible:ring-2 active:bg-sidebar-accent active:text-sidebar-accent-foreground disabled:pointer-events-none disabled:opacity-50 group-has-data-[sidebar=menu-action]/menu-item:pr-8 aria-disabled:pointer-events-none aria-disabled:opacity-50 data-[active=true]:bg-sidebar-primary/12 data-[active=true]:font-semibold data-[active=true]:text-sidebar-primary data-[active=true]:shadow-ui-xs data-[active=true]:before:opacity-100 data-[state=open]:hover:bg-sidebar-accent data-[state=open]:hover:text-sidebar-accent-foreground [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        outline:
          "bg-background shadow-[0_0_0_1px_hsl(var(--sidebar-border))] hover:bg-sidebar-accent hover:text-sidebar-accent-foreground hover:shadow-[0_0_0_1px_hsl(var(--sidebar-accent))]",
      },
      size: {
        default: "h-8 text-sm",
        sm: "h-7 text-xs",
        lg: "h-12 text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function SidebarMenuButton({
  asChild = false,
  isActive = false,
  variant = "default",
  size = "default",
  tooltip,
  className,
  ...props
}: React.ComponentProps<"button"> & {
  asChild?: boolean;
  isActive?: boolean;
  tooltip?: string | React.ComponentProps<typeof TooltipContent>;
} & VariantProps<typeof sidebarMenuButtonVariants>) {
  const Comp = asChild ? Slot : "button";
  const { isMobile } = useSidebar();

  const button = (
    <Comp
      data-slot="sidebar-menu-button"
      data-sidebar="menu-button"
      data-size={size}
      data-active={isActive}
      className={cn(sidebarMenuButtonVariants({ variant, size }), className)}
      {...props}
    />
  );

  if (!tooltip) {
    return button;
  }

  if (typeof tooltip === "string") {
    tooltip = {
      children: tooltip,
    };
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent
        side="right"
        align="center"
        hidden={isMobile}
        {...tooltip}
      />
    </Tooltip>
  );
}

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarTrigger,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
};
