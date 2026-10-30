// The initial command validates broker configuration without reading secrets or
// connecting to production. MCP serving is gated on the selected Go MCP SDK.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"

	"ops-agent/broker/internal/authz"
	"ops-agent/broker/internal/envregistry"
	"ops-agent/broker/internal/redact"
)

func main() {
	if err := run(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(args []string, out, errOut io.Writer) error {
	if len(args) == 0 || args[0] != "check-config" {
		return fmt.Errorf("usage: broker check-config --environments PATH --access PATH --redaction PATH")
	}
	flags := flag.NewFlagSet("check-config", flag.ContinueOnError)
	// Avoid echoing invalid argument values which could contain credentials.
	flags.SetOutput(io.Discard)
	envs := flags.String("environments", "", "environment registry")
	access := flags.String("access", "", "authorization policy")
	rules := flags.String("redaction", "", "additional redaction rules")
	if flags.Parse(args[1:]) != nil || flags.NArg() != 0 || *envs == "" || *access == "" || *rules == "" {
		return fmt.Errorf("check-config requires --environments, --access and --redaction paths")
	}
	f, err := os.Open(*envs)
	if err != nil {
		return fmt.Errorf("cannot open environment registry")
	}
	defer f.Close()
	registry, err := envregistry.Load(f)
	if err != nil {
		return err
	}
	fAccess, err := os.Open(*access)
	if err != nil {
		return fmt.Errorf("cannot open access policy")
	}
	defer fAccess.Close()
	if _, err := authz.Load(fAccess, registry); err != nil {
		return err
	}
	fRules, err := os.Open(*rules)
	if err != nil {
		return fmt.Errorf("cannot open redaction rules")
	}
	defer fRules.Close()
	if _, err := redact.Load(fRules); err != nil {
		return err
	}
	_, err = fmt.Fprintf(out, "configuration valid: %d environment(s); no secrets loaded\n", len(registry.Names()))
	return err
}
