using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Novit.Web.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddCommunityPublications : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "community_publications",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    review_token = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    platform = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    content_type = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    status = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    topic = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    angle = table.Column<string>(type: "character varying(1000)", maxLength: 1000, nullable: false),
                    objective = table.Column<string>(type: "character varying(1000)", maxLength: 1000, nullable: false),
                    caption = table.Column<string>(type: "text", nullable: false),
                    alt_text = table.Column<string>(type: "text", nullable: false),
                    hashtags_json = table.Column<string>(type: "text", nullable: false),
                    strategy_json = table.Column<string>(type: "text", nullable: false),
                    copy_json = table.Column<string>(type: "text", nullable: false),
                    design_json = table.Column<string>(type: "text", nullable: false),
                    evaluation_json = table.Column<string>(type: "text", nullable: false),
                    video_duration_seconds = table.Column<int>(type: "integer", nullable: false),
                    version = table.Column<int>(type: "integer", nullable: false),
                    review_subject = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    last_reviewer_feedback = table.Column<string>(type: "text", nullable: false),
                    reviewer_feedback_history_json = table.Column<string>(type: "text", nullable: false),
                    last_revision_target = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    last_error = table.Column<string>(type: "text", nullable: false),
                    approved_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    rejected_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    published_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    created_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    updated_at = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_community_publications", x => x.id);
                });

            migrationBuilder.CreateIndex(
                name: "idx_community_publications_created_at",
                table: "community_publications",
                column: "created_at");

            migrationBuilder.CreateIndex(
                name: "idx_community_publications_review_token",
                table: "community_publications",
                column: "review_token",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "idx_community_publications_status",
                table: "community_publications",
                column: "status");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "community_publications");
        }
    }
}