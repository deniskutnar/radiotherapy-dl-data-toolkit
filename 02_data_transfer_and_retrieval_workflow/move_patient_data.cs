using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using VMS.TPS.Common.Model.API;
using VMS.TPS.Common.Model.Types;
using EvilDICOM.Network;
using EvilDICOM.Network.SCUOps;

[assembly: ESAPIScript(IsWriteable = true)]

namespace DataTransferByUid
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            try
            {
                using (var app = Application.CreateApplication())
                {
                    Execute(app);
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(ex);
            }
        }

        private static void Execute(Application app)
        {
            var source = new Entity("SOURCE_AE", "SOURCE_HOST", 104);
            var destination = new Entity("DESTINATION_AE", "DESTINATION_HOST", 105);
            var local = Entity.CreateLocal("LOCAL_RESEARCH_AE", 11113);
            var client = new DICOMSCU(local);

            const string csvPath = @"C:\Path\To\filtered_records.csv";
            const string parameterPoolFolder = @"C:\Path\To\parameter_pool";
            const int startingRow = 1;
            const int endingRow = 2;

            var lines = File.ReadAllLines(csvPath);
            int queueCounter = 0;

            for (int rowIndex = startingRow; rowIndex <= endingRow; rowIndex++)
            {
                if (rowIndex < 0 || rowIndex >= lines.Length)
                {
                    continue;
                }

                var values = ParseCsvLine(lines[rowIndex]);
                var patientId = values[0];
                var planId = values[1];
                var courseId = values[2];

                var safePlanId = planId.Replace(':', '~').Replace(',', '~');
                var parameterFileName = $"{patientId}_{courseId}_{safePlanId}_parameters.txt";
                var parameterFilePath = Path.Combine(parameterPoolFolder, parameterFileName);

                Console.WriteLine($"Reading file: {parameterFilePath}");
                var records = File.ReadAllLines(parameterFilePath);

                var selectedPatientId = records[0];
                var imageSeriesUid = records[1];
                var imageStudyUid = records[2];
                var structSetUid = records[3];
                var structSetSeriesUid = records[4];
                var structSetStudyUid = records[5];

                var finder = client.GetCFinder(source);
                var studies = finder.FindStudies(selectedPatientId).ToList();
                var series = finder.FindSeries(studies).ToList();
                var instances = finder.FindInstances(series).ToList();
                var images = finder.FindImages(series).ToList();

                var planImages = series
                    .Where(s => s.Modality == "RTPLAN")
                    .SelectMany(s => finder.FindImages(s))
                    .ToList();
                var doseImages = series
                    .Where(s => s.Modality == "RTDOSE")
                    .SelectMany(s => finder.FindImages(s))
                    .ToList();
                var ctImages = series
                    .Where(s => s.Modality == "CT")
                    .SelectMany(s => finder.FindImages(s))
                    .ToList();
                var rtStructImages = series
                    .Where(s => s.Modality == "RTSTRUCT")
                    .SelectMany(s => finder.FindImages(s))
                    .ToList();
                var rtImageImages = series
                    .Where(s => s.Modality == "RTIMAGE")
                    .SelectMany(s => finder.FindImages(s))
                    .ToList();

                Console.WriteLine("-------------------------------------------------------------");
                Console.WriteLine($"Patient ID: {selectedPatientId}");
                Console.WriteLine($"Studies found: {studies.Count}");
                Console.WriteLine($"Series found : {series.Count}");
                Console.WriteLine($"Instances    : {instances.Count}");
                Console.WriteLine($"Images       : {images.Count}");
                Console.WriteLine();

                foreach (var group in series.GroupBy(s => s.Modality))
                {
                    Console.WriteLine($"{group.Key}: {group.Count()}");
                }

                foreach (var study in studies)
                {
                    if (study.StudyInstanceUID == imageStudyUid)
                    {
                        Console.WriteLine($"Matched image study UID     : {study.StudyInstanceUID}");
                    }

                    if (study.StudyInstanceUID == structSetStudyUid)
                    {
                        Console.WriteLine($"Matched structure study UID : {study.StudyInstanceUID}");
                    }
                }

                foreach (var currentSeries in series)
                {
                    if (currentSeries.SeriesInstanceUID == imageSeriesUid)
                    {
                        Console.WriteLine($"Matched image series UID     : {currentSeries.SeriesInstanceUID}");
                    }

                    if (currentSeries.SeriesInstanceUID == structSetSeriesUid)
                    {
                        Console.WriteLine($"Matched structure series UID : {currentSeries.SeriesInstanceUID}");
                    }
                }

                Console.WriteLine();
                Console.WriteLine($"RTPLAN image objects   : {planImages.Count}");
                Console.WriteLine($"RTDOSE image objects   : {doseImages.Count}");
                Console.WriteLine($"CT image objects       : {ctImages.Count}");
                Console.WriteLine($"RTSTRUCT image objects : {rtStructImages.Count}");
                Console.WriteLine($"RTIMAGE image objects  : {rtImageImages.Count}");
                Console.WriteLine();

                foreach (var rtStruct in rtStructImages)
                {
                    if (rtStruct.SOPInstanceUID == structSetUid)
                    {
                        Console.WriteLine($"Matched RTSTRUCT UID         : {rtStruct.SOPInstanceUID}");
                    }
                }

                var mover = client.GetCMover(source);
                ushort messageId = 1;

                foreach (var currentSeries in series.Where(s => s.SeriesInstanceUID == imageSeriesUid))
                {
                    Console.WriteLine("Sending CT image series...");
                    PrintMoveResponse(mover.SendCMove(currentSeries, destination.AeTitle, ref messageId));
                }

                foreach (var rtStruct in rtStructImages.Where(i => i.SOPInstanceUID == structSetUid))
                {
                    Console.WriteLine("Sending RTSTRUCT...");
                    PrintMoveResponse(mover.SendCMove(rtStruct, destination.AeTitle, ref messageId));
                }

                queueCounter++;
                Console.WriteLine();
                Console.WriteLine($"Queue progress: {queueCounter} / {endingRow - startingRow + 1}");
                Console.WriteLine("-------------------------------------------------------------");
            }

            Console.WriteLine("Selective transfer completed.");
            Console.Read();
        }

        private static void PrintMoveResponse(dynamic response)
        {
            if (response == null)
            {
                Console.WriteLine("Error: C-MOVE returned a null response.");
                return;
            }

            Console.WriteLine("DICOM C-MOVE results:");
            Console.WriteLine($"Completed operations : {response.NumberOfCompletedOps}");
            Console.WriteLine($"Failed operations    : {response.NumberOfFailedOps}");
            Console.WriteLine($"Remaining operations : {response.NumberOfRemainingOps}");
            Console.WriteLine($"Warning operations   : {response.NumberOfWarningOps}");
            Console.WriteLine($"Status               : {response.Status}");
            Console.WriteLine();
        }

        private static string[] ParseCsvLine(string line)
        {
            var values = new List<string>();
            var builder = new StringBuilder();
            bool inQuotes = false;

            foreach (var character in line)
            {
                if (character == '"')
                {
                    inQuotes = !inQuotes;
                    continue;
                }

                if (character == ',' && !inQuotes)
                {
                    values.Add(builder.ToString());
                    builder.Clear();
                    continue;
                }

                builder.Append(character);
            }

            values.Add(builder.ToString());
            return values.ToArray();
        }
    }
}
