locals {
  create_crawler_security_group = var.crawler_security_group_id == null
  crawler_security_group_id = local.create_crawler_security_group ? (
    aws_security_group.crawler[0].id
  ) : var.crawler_security_group_id
  tags = merge(var.tags, {
    Application = "inform-crawler"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_security_group" "crawler" {
  count = local.create_crawler_security_group ? 1 : 0

  name_prefix            = "inform-crawler-${var.environment}-"
  description            = "Ephemeral crawler: no inbound rules"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true
  tags                    = local.tags
}

resource "aws_vpc_security_group_egress_rule" "crawler_ipv4" {
  count = local.create_crawler_security_group ? 1 : 0

  security_group_id = aws_security_group.crawler[0].id
  description       = "Crawler Internet and AWS public-service access"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_crawler" {
  security_group_id            = var.main_db_security_group_id
  referenced_security_group_id = local.crawler_security_group_id
  description                  = "Private PostgreSQL access from ephemeral crawler"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
