# generated by fastapi-codegen:
#   filename:  ./refget-openapi.yaml
#   timestamp: 2024-06-04T14:55:19+00:00

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import AnyUrl, BaseModel, Field


class Alias(BaseModel):
    alias: str = Field(
        ...,
        description="Free text alias for a given sequence",
        json_schema_extra={
            "examples": [
                {
                    "alias": "chr1",
                }
            ]
        },
    )
    naming_authority: str = Field(
        ..., description="Name of the authority, which issued the given alias"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Foo",
                    "description": "A very nice Item",
                    "price": 35.4,
                    "tax": 3.2,
                }
            ]
        }
    }


class Refget(BaseModel):
    circular_supported: bool = Field(
        ..., description="Indicates if the service supports circular location queries"
    )
    subsequence_limit: Optional[int] = Field(
        None,
        description="Maximum length of sequence which may be requested using start and/or end query parameters",
    )
    algorithms: List[str]
    identifier_types: Optional[List[str]] = None


class Organization(BaseModel):
    name: str = Field(
        ...,
        description="Name of the organization responsible for the service",
        json_schema_extra={"example": "My organization"},
    )
    url: AnyUrl = Field(
        ...,
        description="URL of the website of the organization (RFC 3986 format)",
        json_schema_extra={"example": "https://example.com"},
    )


class ServiceType(BaseModel):
    group: str = Field(
        ...,
        description="Namespace in reverse domain name format. Use `org.ga4gh` for implementations compliant with official GA4GH specifications. For services with custom APIs not standardized by GA4GH, or implementations diverging from official GA4GH specifications, use a different namespace (e.g. your organization's reverse domain name).",
        json_schema_extra={"example": "org.ga4gh"},
    )
    artifact: str = Field(
        ...,
        description="Name of the API or GA4GH specification implemented. Official GA4GH types should be assigned as part of standards approval process. Custom artifacts are supported.",
        json_schema_extra={"example": "beacon"},
    )
    version: str = Field(
        ...,
        description="Version of the API or specification. GA4GH specifications use semantic versioning.",
        json_schema_extra={"example": "1.0.0"},
    )


class Metadata1(BaseModel):
    id: str = Field(
        ...,
        description="Query identifier. Normally the default checksum for a given service",
        json_schema_extra={"example": "6681ac2f62509cfc220d78751b8dc524"},
    )
    md5: str = Field(
        ...,
        description="MD5 checksum of the reference sequence",
        json_schema_extra={"example": "6681ac2f62509cfc220d78751b8dc524"},
    )
    trunc512: Optional[str] = Field(
        None,
        description="Truncated, to 48 characters, SHA-512 checksum of the reference sequence encoded as a HEX string. No longer a preferred serialisation of the SHA-512",
        json_schema_extra={
            "example": "959cb1883fc1ca9ae1394ceb475a356ead1ecceff5824ae7"
        },
    )
    ga4gh: Optional[str] = Field(
        None,
        description="A ga4gh identifier used to identify the sequence. This is a   [base64url](defined in RFC4648 §5) representation of the 1st 24 bytes from a SHA-512 digest of normalised sequence. This is the preferred method of  representing the SHA-512 sequence digest.",
        json_schema_extra={"example": "ga4gh:SQ.aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2"},
    )
    length: int = Field(
        ..., description="An decimal integer of the length of the reference sequence"
    )
    aliases: List[Alias]


class Metadata(BaseModel):
    metadata: Optional[Metadata1] = None


class Service(BaseModel):
    id: str = Field(
        ...,
        description="Unique ID of this service. Reverse domain name notation is recommended, though not required. The identifier should attempt to be globally unique so it can be used in downstream aggregator services e.g. Service Registry.",
        json_schema_extra={"example": "org.ga4gh.myservice"},
    )
    name: str = Field(
        ...,
        description="Name of this service. Should be human readable.",
        json_schema_extra={"example": "My project"},
    )
    type: ServiceType
    description: Optional[str] = Field(
        None,
        description="Description of the service. Should be human readable and provide information about the service.",
        json_schema_extra={"example": "This service provides..."},
    )
    organization: Organization = Field(
        ..., description="Organization providing the service"
    )
    contactUrl: Optional[AnyUrl] = Field(
        None,
        description="URL of the contact for the provider of this service, e.g. a link to a contact form (RFC 3986 format), or an email (RFC 2368 format).",
        json_schema_extra={"example": "mailto:support@example.com"},
    )
    documentationUrl: Optional[AnyUrl] = Field(
        None,
        description="URL of the documentation of this service (RFC 3986 format). This should help someone learn how to use your service, including any specifics required to access data, e.g. authentication.",
        json_schema_extra={"example": "https://docs.myservice.example.com"},
    )
    createdAt: Optional[datetime] = Field(
        None,
        description="Timestamp describing when the service was first deployed and available (RFC 3339 format)",
        json_schema_extra={"example": "2019-06-04T12:58:19Z"},
    )
    updatedAt: Optional[datetime] = Field(
        None,
        description="Timestamp describing when the service was last updated (RFC 3339 format)",
        json_schema_extra={"example": "2019-06-04T12:58:19Z"},
    )
    environment: Optional[str] = Field(
        None,
        description="Environment the service is running in. Use this to distinguish between production, development and testing/staging deployments. Suggested values are prod, test, dev, staging. However this is advised and not enforced.",
        json_schema_extra={"example": "test"},
    )
    version: str = Field(
        ...,
        description="Version of the service being described. Semantic versioning is recommended, but other identifiers, such as dates or commit hashes, are also allowed. The version should be changed whenever the service is updated.",
        json_schema_extra={"example": "1.0.0"},
    )


class RefgetServiceInfo(Service):
    refget: Refget
