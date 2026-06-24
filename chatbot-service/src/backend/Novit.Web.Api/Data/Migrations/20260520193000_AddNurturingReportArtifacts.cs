using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Novit.Web.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddNurturingReportArtifacts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "artifact_json",
                table: "nurturing_emails",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "executive_summary",
                table: "nurturing_emails",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "report_title",
                table: "nurturing_emails",
                type: "character varying(500)",
                maxLength: 500,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "artifact_json",
                table: "nurturing_emails");

            migrationBuilder.DropColumn(
                name: "executive_summary",
                table: "nurturing_emails");

            migrationBuilder.DropColumn(
                name: "report_title",
                table: "nurturing_emails");
        }
    }
}