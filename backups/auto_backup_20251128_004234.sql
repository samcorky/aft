-- AFT Automatic Database Backup
-- Alembic Version: 008
-- Backup Date: 2025-11-28T00:42:34.195943
--

/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-11.8.3-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: db    Database: aft_db
-- ------------------------------------------------------
-- Server version	9.5.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
set autocommit=0;
INSERT INTO `alembic_version` VALUES
('008');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `boards`
--

DROP TABLE IF EXISTS `boards`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `boards` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  PRIMARY KEY (`id`),
  KEY `ix_boards_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=646 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `boards`
--

LOCK TABLES `boards` WRITE;
/*!40000 ALTER TABLE `boards` DISABLE KEYS */;
set autocommit=0;
/*!40000 ALTER TABLE `boards` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `cards`
--

DROP TABLE IF EXISTS `cards`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `cards` (
  `id` int NOT NULL AUTO_INCREMENT,
  `column_id` int NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` varchar(2000) DEFAULT NULL,
  `order` int NOT NULL DEFAULT '0',
  `archived` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `ix_cards_id` (`id`),
  KEY `ix_cards_column_id` (`column_id`),
  KEY `ix_cards_archived` (`archived`),
  CONSTRAINT `cards_ibfk_1` FOREIGN KEY (`column_id`) REFERENCES `columns` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1234 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cards`
--

LOCK TABLES `cards` WRITE;
/*!40000 ALTER TABLE `cards` DISABLE KEYS */;
set autocommit=0;
/*!40000 ALTER TABLE `cards` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `checklist_items`
--

DROP TABLE IF EXISTS `checklist_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `checklist_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `card_id` int NOT NULL,
  `name` varchar(500) NOT NULL,
  `checked` tinyint(1) NOT NULL DEFAULT '0',
  `order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `ix_checklist_items_id` (`id`),
  KEY `ix_checklist_items_card_id` (`card_id`),
  CONSTRAINT `checklist_items_ibfk_1` FOREIGN KEY (`card_id`) REFERENCES `cards` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=655 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `checklist_items`
--

LOCK TABLES `checklist_items` WRITE;
/*!40000 ALTER TABLE `checklist_items` DISABLE KEYS */;
set autocommit=0;
/*!40000 ALTER TABLE `checklist_items` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `columns`
--

DROP TABLE IF EXISTS `columns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `columns` (
  `id` int NOT NULL AUTO_INCREMENT,
  `board_id` int NOT NULL,
  `name` varchar(255) NOT NULL,
  `order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `ix_columns_id` (`id`),
  KEY `ix_columns_board_id` (`board_id`),
  CONSTRAINT `columns_ibfk_1` FOREIGN KEY (`board_id`) REFERENCES `boards` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=886 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `columns`
--

LOCK TABLES `columns` WRITE;
/*!40000 ALTER TABLE `columns` DISABLE KEYS */;
set autocommit=0;
/*!40000 ALTER TABLE `columns` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `comments`
--

DROP TABLE IF EXISTS `comments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `comments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `card_id` int NOT NULL,
  `comment` text NOT NULL,
  `order` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_comments_id` (`id`),
  KEY `ix_comments_card_id` (`card_id`),
  KEY `ix_comments_order` (`order`),
  CONSTRAINT `comments_ibfk_1` FOREIGN KEY (`card_id`) REFERENCES `cards` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `comments`
--

LOCK TABLES `comments` WRITE;
/*!40000 ALTER TABLE `comments` DISABLE KEYS */;
set autocommit=0;
/*!40000 ALTER TABLE `comments` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Table structure for table `settings`
--

DROP TABLE IF EXISTS `settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `key` varchar(255) NOT NULL,
  `value` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `key` (`key`),
  UNIQUE KEY `ix_settings_key` (`key`),
  KEY `ix_settings_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `settings`
--

LOCK TABLES `settings` WRITE;
/*!40000 ALTER TABLE `settings` DISABLE KEYS */;
set autocommit=0;
INSERT INTO `settings` VALUES
(1,'default_board','null'),
(2,'backup_enabled','true'),
(3,'backup_frequency_value','1'),
(4,'backup_frequency_unit','\"minutes\"'),
(5,'backup_start_time','\"00:15\"'),
(6,'backup_retention_count','2'),
(7,'backup_last_run','\"2025-11-28T00:40:41.381175\"');
/*!40000 ALTER TABLE `settings` ENABLE KEYS */;
UNLOCK TABLES;
commit;

--
-- Dumping routines for database 'aft_db'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2025-11-28  0:42:34
