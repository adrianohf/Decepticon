// Decepticon Attack Chain Graph — Schema Init
// Run once after Neo4j starts: cypher-shell < scripts/init_neo4j.cypher

// ── Uniqueness constraints (dedup by deterministic key) ──────────────────
CREATE CONSTRAINT host_ip IF NOT EXISTS FOR (h:Host) REQUIRE h.ip IS UNIQUE;
CREATE CONSTRAINT service_key IF NOT EXISTS FOR (s:Service) REQUIRE s.key IS UNIQUE;
CREATE CONSTRAINT url_norm IF NOT EXISTS FOR (u:URL) REQUIRE u.normalized IS UNIQUE;
CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (c:CVE) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT vuln_key IF NOT EXISTS FOR (v:Vulnerability) REQUIRE v.key IS UNIQUE;
CREATE CONSTRAINT cred_key IF NOT EXISTS FOR (c:Credential) REQUIRE c.key IS UNIQUE;
CREATE CONSTRAINT user_key IF NOT EXISTS FOR (u:User) REQUIRE u.key IS UNIQUE;
CREATE CONSTRAINT domain_fqdn IF NOT EXISTS FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE;
CREATE CONSTRAINT network_cidr IF NOT EXISTS FOR (n:Network) REQUIRE n.cidr IS UNIQUE;
CREATE CONSTRAINT finding_key IF NOT EXISTS FOR (f:Finding) REQUIRE f.key IS UNIQUE;
CREATE CONSTRAINT hypothesis_key IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT crown_key IF NOT EXISTS FOR (c:CrownJewel) REQUIRE c.key IS UNIQUE;
CREATE CONSTRAINT engagement_slug IF NOT EXISTS FOR (e:Engagement) REQUIRE e.slug IS UNIQUE;
// Legacy KGNode label used by neo4j_store.py
CREATE CONSTRAINT kgnode_id IF NOT EXISTS FOR (n:KGNode) REQUIRE n.id IS UNIQUE;

// ── Indexes (objective-selector hot path) ───────────────────────────────
CREATE INDEX host_explored IF NOT EXISTS FOR (h:Host) ON (h.explored);
CREATE INDEX host_compromised IF NOT EXISTS FOR (h:Host) ON (h.compromised);
CREATE INDEX service_version IF NOT EXISTS FOR (s:Service) ON (s.product, s.version);
CREATE INDEX vuln_severity IF NOT EXISTS FOR (v:Vulnerability) ON (v.cvss, v.exploited);
CREATE INDEX hypothesis_conf IF NOT EXISTS FOR (h:Hypothesis) ON (h.confidence);
CREATE INDEX finding_type IF NOT EXISTS FOR (f:Finding) ON (f.type);
CREATE INDEX technique_id_idx IF NOT EXISTS FOR (t:Technique) ON (t.id);
